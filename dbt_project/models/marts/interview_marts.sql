-- Mart model calculating consolidated interview round scores
with aggregated_logs as (
    select
        interview_id,
        count(*) as total_exchanges,
        avg(score) as average_score,
        max(score) as peak_score,
        min(created_date) as session_date
    from main.interview_logs
    where speaker = 'USER'
    group by interview_id
)

select
    al.interview_id,
    al.total_exchanges,
    round(al.average_score, 2) as average_score,
    al.peak_score,
    al.session_date,
    i.application_id,
    a.company_name,
    a.job_title
from aggregated_logs al
join main.interviews i on al.interview_id = i.id
join main.applications a on i.application_id = a.id
order by al.session_date desc
