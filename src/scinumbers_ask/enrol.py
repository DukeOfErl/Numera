"""Enrolling one tester: mint a capped credential, record the account, or undo.

Two systems have to agree -- OpenRouter holds the credential, the accounts table
holds who may use it -- and there is no transaction across them. So the order is
chosen for what a half-done enrolment leaves behind:

**Mint, then insert, and revoke if the insert fails.** The other order writes a
row with no key, which is a door of its own (`NO_CREDENTIAL`): the tester signs
in, is told no credential has been issued, and the operator sees an account that
looks deliberately keyless rather than half-made. A minted key nobody refers to
costs nothing while it exists and is revoked on the way out.

**Every refusal is in `enrol`, not in `main`.** The command keeps the wording;
the operation keeps the refusal. A second caller -- a test, a future page, a
script an operator writes -- meets the same guards, which is the point: the one
that matters here is that nothing issues an *uncapped* credential, because
ADR-0780's case for storing keys in the clear rests entirely on every key having
a cap.

**This raises where `allowance.py` swallows**, for the reason `neon.py` gives at
the same seam: an operator is watching a command they typed.

The management key mints and cannot itself call completion endpoints. It is read
from the environment for one invocation and never stored beside the app.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass

from . import accounts, neon, trail_store
from .accounts import Account, AlreadyEnrolled
from .permissions import Role

KEYS_ENDPOINT = "https://openrouter.ai/api/v1/keys"

#: As `neon.TIMEOUT_S`, and for the same reason.
TIMEOUT_S = 30

#: The only reset this command issues. A tester who exhausts their cap recovers
#: on their own instead of the operator servicing an unlock, and a spent key
#: already surfaces as its own ending (ADR-0600).
LIMIT_RESET = "monthly"


class Uncapped(ValueError):
    """The cap was missing, zero or negative, so nothing was issued."""


class MintFailed(RuntimeError):
    """OpenRouter did not return a usable key, or returned one that is not what
    was asked for. Anything it did create has been revoked."""


class NothingEnrolled(RuntimeError):
    """The account could not be recorded. The credential has been withdrawn."""


class KeyLeftBehind(RuntimeError):
    """The account could not be recorded *and* the credential could not be
    withdrawn. Names the key so the operator can revoke it by hand -- this is the
    one outcome that leaves work for a person, so it must not be silent."""


@dataclass(frozen=True)
class Minted:
    """A freshly issued credential: the secret, and the handle that names it later."""

    key: str
    hash: str


def _post(url: str, management_key: str, body: dict | None, opener, method: str = "POST") -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {management_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with opener(request, timeout=TIMEOUT_S) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def revoke(management_key: str, key_hash: str, *, opener=urllib.request.urlopen) -> None:
    """Withdraw a credential. Raises if the provider refuses."""
    _post(f"{KEYS_ENDPOINT}/{key_hash}", management_key, None, opener, method="DELETE")


def mint(
    management_key: str,
    *,
    name: str,
    limit_usd: float,
    opener=urllib.request.urlopen,
) -> Minted:
    """Issue one runtime credential capped at `limit_usd`, renewing monthly.

    **The echo is checked, and a key that came back wrong is revoked rather than
    handed out.** What is being verified is not that the call succeeded but that
    the credential has the property the whole storage decision rests on: a key
    created with no cap, or with a cap this command did not ask for, is a key
    whose worst case is unbounded. A `limit_reset` the create call did not honour
    is retried once as a `PATCH`, because that is a field OpenRouter has
    documented on both endpoints; a `limit` that comes back wrong is not retried,
    because a provider disagreeing about the number is not a provider to argue
    with.
    """
    payload = _post(
        KEYS_ENDPOINT,
        management_key,
        {"name": name, "limit": limit_usd, "limit_reset": LIMIT_RESET},
        opener,
    )
    key = payload.get("key")
    echoed = payload.get("data") or {}
    key_hash = echoed.get("hash")
    if not key_hash:
        # Nothing names what may have been created, so there is nothing to
        # withdraw and the operator has to be told that plainly rather than
        # reassured by this class's docstring.
        raise MintFailed(
            "OpenRouter returned no key hash, so if a credential was created "
            "nothing here can name or withdraw it. Check the dashboard."
        )
    if not key:
        # The handle came back and the secret did not. A capped key exists at the
        # provider and this process is the only thing that knows its hash, so
        # withdrawing it here is the difference between a bounded mistake and a
        # live credential nobody can name.
        _revoke_quietly(management_key, key_hash, opener)
        raise MintFailed("OpenRouter returned a key hash but no key; the credential was withdrawn")
    if not _same_amount(echoed.get("limit"), limit_usd):
        _revoke_quietly(management_key, key_hash, opener)
        raise MintFailed(f"asked for a cap of {limit_usd} and got {echoed.get('limit')!r}")
    if echoed.get("limit_reset") != LIMIT_RESET:
        try:
            patched = _post(
                f"{KEYS_ENDPOINT}/{key_hash}",
                management_key,
                {"limit_reset": LIMIT_RESET},
                opener,
                method="PATCH",
            )
        except Exception:
            # The two *checked* failures below withdraw the key; a transport
            # failure between them used to escape without doing so, leaving a
            # live credential and no `Minted` for `enrol` to compensate from. The
            # guarantee has to hold for the way this call fails, not only for the
            # answers it gives.
            _revoke_quietly(management_key, key_hash, opener)
            raise
        if (patched.get("data") or patched).get("limit_reset") != LIMIT_RESET:
            _revoke_quietly(management_key, key_hash, opener)
            raise MintFailed(f"the credential would not take a {LIMIT_RESET} reset")
    return Minted(key=key, hash=key_hash)


def _same_amount(echoed, asked: float) -> bool:
    """Whether the provider's cap is the one asked for, across JSON's number types."""
    try:
        return float(echoed) == float(asked)
    except (TypeError, ValueError):
        return False


def _revoke_quietly(management_key: str, key_hash: str, opener) -> None:
    """Undo on a path that is already failing, without replacing its reason.

    The caller is about to raise something the operator needs to read; a second
    exception from the cleanup would hide it. The hash goes to stderr so nothing
    is lost either way.
    """
    try:
        revoke(management_key, key_hash, opener=opener)
    except Exception as exc:  # noqa: BLE001 - the original failure is the one to report
        print(f"could not revoke {key_hash}: {exc}", file=sys.stderr)


def checked(role: Role | str, limit_usd: float) -> Role:
    """The two refusals that need nothing but the arguments. Returns the role.

    Split out so the command can run them **before** it resolves a branch, and
    `enrol` can run them again before it mints -- the same rule, one expression
    of it. The guard belongs to the operation, which is why `enrol` still calls
    it; the command calls it too because otherwise `--limit-usd 0` costs two live
    control-plane calls before anything says no.
    """
    if limit_usd is None or not limit_usd > 0:
        raise Uncapped(
            f"a cap of {limit_usd!r} is not a cap. Every credential this issues is capped, "
            "because that is what makes storing it in the clear defensible (ADR-0780)"
        )
    try:
        return Role(role)
    except ValueError as exc:
        raise ValueError(f"{role!r} is not one of {[r.value for r in Role]}") from exc


def enrol(
    engine,
    management_key: str,
    email: str,
    role: Role | str,
    limit_usd: float,
    *,
    opener=urllib.request.urlopen,
) -> Account:
    """Issue a credential and record the account. The operation, with its guards.

    Refuses before touching anything: a cap that is not positive, and a role that
    is not one of `Role`'s. Both are the operator's typo, and both are free to
    catch here -- `mint` is what costs something.
    """
    role = checked(role, limit_usd)
    minted = mint(management_key, name=email, limit_usd=limit_usd, opener=opener)
    try:
        return accounts.insert(engine, email, role, minted.key)
    except Exception as exc:
        try:
            revoke(management_key, minted.hash, opener=opener)
        except Exception as cleanup:  # noqa: BLE001 - reported, not swallowed
            raise KeyLeftBehind(
                f"{email} was not enrolled and its credential {minted.hash} could not be "
                f"withdrawn ({cleanup}). Revoke it at OpenRouter by hand."
            ) from exc
        if isinstance(exc, AlreadyEnrolled):
            raise
        raise NothingEnrolled(f"{email} was not enrolled; its credential was withdrawn") from exc


# --- the command ------------------------------------------------------------------

#: Named where they are read, so a missing one is reported by the name the
#: operator has to set rather than by what it is for.
MANAGEMENT_KEY_ENV = "OPENROUTER_MANAGEMENT_KEY"
NEON_API_KEY_ENV = "NEON_API_KEY"
NEON_PROJECT_ENV = "NEON_PROJECT_ID"

NO_BRANCH = (
    "no branch named. The row has to land in the branch the deployed app reads, and "
    "none is assumed -- naming the wrong one enrols a tester the app will never find. "
    "Add --branch alpha, or --branch dev for a rehearsal."
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scinumbers-enrol",
        description="Issue a capped credential and enrol one account.",
    )
    parser.add_argument("email")
    parser.add_argument("role", choices=[r.value for r in Role])
    parser.add_argument("--limit-usd", type=float, required=True, help="monthly cap, in dollars")
    # Required and with no default, deliberately: see NO_BRANCH. argparse's own
    # "the following arguments are required" says nothing about why, and this is
    # the one mistake whose symptom appears somewhere else entirely -- the tester
    # is told they are not enrolled while the operator is looking at their row.
    parser.add_argument(
        "--branch",
        # Not `required=True`, so that the refusal is this module's sentence
        # rather than argparse's -- but the help has to say so, or `--help` shows
        # `[--branch BRANCH]` and reads as optional, which is the opposite of the
        # point.
        help="REQUIRED, no default: the Neon branch to enrol into, e.g. alpha",
    )
    parser.add_argument("--database", default=neon.DEFAULT_DATABASE)
    parser.add_argument("--role-name", default=neon.DEFAULT_ROLE, help="Neon database role")
    return parser


def main(argv: list[str] | None = None) -> int:
    """`scinumbers-enrol`. Refusals come back as one sentence and a non-zero exit."""
    args = _parser().parse_args(argv)
    if not args.branch:
        print(NO_BRANCH, file=sys.stderr)
        return 2
    missing = [
        name
        for name in (MANAGEMENT_KEY_ENV, NEON_API_KEY_ENV, NEON_PROJECT_ENV)
        if not os.environ.get(name)
    ]
    if missing:
        print(f"set {' and '.join(missing)} before enrolling anyone", file=sys.stderr)
        return 2

    try:
        # Before the branch is resolved, so a mistyped cap costs no live call.
        # `enrol` checks again; this is the same rule read twice, not a second
        # rule that could drift.
        checked(args.role, args.limit_usd)
    except (Uncapped, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    api_key = os.environ[NEON_API_KEY_ENV]
    project = os.environ[NEON_PROJECT_ENV]
    try:
        # Resolved before anything is minted, so a mistyped branch costs nothing.
        branch = neon.branch_id(api_key, project, args.branch)
        url = neon.connection_url(
            api_key, project, branch, database=args.database, role=args.role_name
        )
    except Exception as exc:  # noqa: BLE001 - one sentence for the operator
        print(str(exc), file=sys.stderr)
        return 1

    engine = trail_store.engine_from_url(url)
    try:
        account = enrol(
            engine,
            os.environ[MANAGEMENT_KEY_ENV],
            args.email,
            args.role,
            args.limit_usd,
        )
    except Exception as exc:  # noqa: BLE001 - every refusal already says what it is
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    # The credential is not here, and not on any other path out of this command:
    # it is looked up by the system and seen by nobody, including the operator
    # who issued it (ADR-0820).
    print(
        f"enrolled {account.email} as {account.role.value} in {args.branch}, "
        f"capped at ${args.limit_usd:.2f} a month"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point is the tested path
    raise SystemExit(main())
