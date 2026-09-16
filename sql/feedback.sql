-- Reading the feedback back.
--
-- Every rating and comment is a row in `trail`, the same append-only table the
-- deterministic trail writes to: a verdict is `feedback.verdict` and a comment is
-- `feedback.comment`, both carrying the `question_id` of the answer they are
-- about. That identifier is the join — it is what the question's own rows
-- (`question.asked`, `search`, `question.answered`) are keyed on, so a rating can
-- always be read next to what the question actually retrieved.
--
-- Run these against the Neon database in `[connections.usage]`. Read-only; none
-- of them writes.
--
-- **Every query here was run against the `dev` branch on 2026-09-16**, which is
-- how they stopped being guesses: 25 verdicts, 12 comments, and query 3 correctly
-- pulling `100001` and `100002` out of free prose written as "checking entry
-- 100001" and "not sure about 100002".
--
-- What that run does *not* establish, for queries 2 and 2b: every rating on `dev`
-- predates `add-question-and-answer-records`, so `question`, `answer`, `cited`
-- and `retrieved` came back null on all 25 rows. The left joins were confirmed to
-- keep those rows rather than drop them, and to return 25 rather than fanning
-- out — but the populated case has only been exercised against the test suite,
-- not against real rows. First rating collected after this change is the one to
-- check them on.
--
-- Query 5 is still the one to run first when something looks wrong, because it
-- filters on nothing: an empty result there means no feedback, not a bad query.
--
-- Reaching Neon from a sandboxed shell needs its SQL-over-HTTP endpoint rather
-- than a Postgres connection — `POST https://<host>/sql` with the connection
-- string in a `Neon-Connection-String` header. Port 5432 does not resolve.
--
-- **A thumbs-down rate is not an error rate.** People who rate are not a sample
-- of people who read: someone who spots a wrong number is far likelier to say so
-- than someone whose answer was fine, and both are rarer than the reader who says
-- nothing. These queries answer "what do people complain about". They do not
-- answer "how often is it wrong", and the first person to quote a percentage from
-- them will have got it from somewhere else. (ADR-0740.)


-- 1. Ratings per day. `run_label` is kept apart because a figure pooled across
--    dev runs and real ones describes neither.
select
    date(at)                                         as day,
    run_label,
    count(*) filter (where detail ->> 'verdict' = 'up')   as up,
    count(*) filter (where detail ->> 'verdict' = 'down') as down,
    count(*)                                         as rated
from trail
where event = 'feedback.verdict'
group by 1, 2
order by 1 desc, 2;


-- 2. Ratings per question, beside the question that was asked and the answer
--    that was rated. This is the query the feedback exists for: without the last
--    two columns a row reads "answer c23c83c16324 was wrong" and stops there.
--
--    Left joins throughout, and deliberately. Most ratings carry no comment, so
--    an inner join there would silently answer a different question; and ratings
--    collected before `add-question-and-answer-records` landed have no
--    `question.asked` or `answer.given` row at all — those questions were never
--    kept anywhere and cannot be backfilled. An inner join would drop them
--    without saying so, which is worse than a visible null.
select
    v.at,
    v.question_id,
    v.session_id,
    v.run_label,
    v.detail ->> 'verdict' as verdict,
    c.detail ->> 'comment'  as comment,
    q.detail ->> 'question' as question,
    a.detail ->> 'answer'   as answer
from trail v
left join trail c
       on c.question_id = v.question_id
      and c.event = 'feedback.comment'
left join trail q
       on q.question_id = v.question_id
      and q.event = 'question.asked'
left join trail a
       on a.question_id = v.question_id
      and a.event = 'answer.given'
where v.event = 'feedback.verdict'
order by v.at desc;


-- 2b. What a rated answer actually stood on: the entries it cited, and the wider
--     set it had retrieved. Separate from query 2 because the two sets are
--     arrays and joining them in would repeat the answer text on every row a
--     reader scrolls past.
--
--     `cited` is what the answer attributed a number to; `retrieved` is
--     everything in front of it. A thumbs-down where the reader names an entry in
--     `retrieved` but not in `cited` is the interesting case: the evidence was
--     there and the answer did not use it.
select
    v.at,
    v.question_id,
    v.detail ->> 'verdict' as verdict,
    e.detail -> 'cited'     as cited,
    e.detail -> 'retrieved' as retrieved,
    jsonb_array_length(e.detail -> 'retrieved') as retrieved_count
from trail v
left join trail e
       on e.question_id = v.question_id
      and e.event = 'answer.evidence'
where v.event = 'feedback.verdict'
order by v.at desc;


-- 3. Every comment naming an entry identifier, which is what the hint asks for
--    and the evidence for whether per-entry rating is worth building.
--
--    Six digits or more, as a whole number: BNIDs in this corpus are six digits,
--    and `\m`/`\M` are Postgres's word boundaries. Without them "100002" matches
--    inside a longer run of digits and a year or a quantity reads as an entry.
--    The regexp is deliberately loose about the surrounding words — readers write
--    "BNID 102345", "102345" and "entry 102345", and asking for the prefix would
--    drop the two commonest forms.
select
    at,
    question_id,
    session_id,
    detail ->> 'comment' as comment,
    (
        select array_agg(distinct m[1])
        from regexp_matches(detail ->> 'comment', '\m(\d{6,})\M', 'g') as m
    ) as entry_ids
from trail
where event = 'feedback.comment'
  and detail ->> 'comment' ~ '\m\d{6,}\M'
order by at desc;


-- 4. All comments, including those naming no entry. Query 3 filters, and a filter
--    is the one thing you cannot check by reading its own output: this is the
--    population it drew from, so the two can be compared.
select at, question_id, run_label, detail ->> 'comment' as comment
from trail
where event = 'feedback.comment'
order by at desc;


-- 5. Is anything arriving at all? The first thing to run when a rating seems to
--    have gone missing — recording fails open, so a failed write is silent to the
--    reader and leaves no row here to find. `complain()` puts the reason on the
--    app's stderr, which on Community Cloud is the log pane.
select
    event,
    count(*)  as rows,
    min(at)   as first_seen,
    max(at)   as last_seen
from trail
group by event
order by 2 desc;
