create table if not exists pension_case (
    pension_case_id text primary key,
    pensioner_uin text not null,
    spouse_uin text,
    marriage_mrn text,
    pension_status text not null,
    payment_status text not null,
    survivor_eligible boolean not null,
    last_payment_date date,
    account_life_status text not null,
    observed_at timestamptz not null,
    source_system text not null
);

create index if not exists pension_case_pensioner_uin_idx on pension_case (pensioner_uin);
create index if not exists pension_case_spouse_uin_idx on pension_case (spouse_uin);

create table if not exists sipf_pension_payment (
    pensioner_uin text primary key,
    payment_status text not null
);

create table if not exists sipf_survivor_benefit (
    spouse_uin text primary key,
    survivor_eligible boolean not null
);
