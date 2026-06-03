-- Staging model for Kanban Job Applications
with source_data as (
    select
        id as application_id,
        trim(company_name) as company_name,
        trim(job_title) as job_title,
        job_url,
        job_description,
        upper(status) as application_status,
        salary_range,
        notes,
        applied_date,
        updated_date
    from main.applications
)

select * from source_data
