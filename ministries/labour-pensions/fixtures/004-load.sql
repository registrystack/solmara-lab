create temporary table pension_case_fixture
    (like pension_case including defaults);

copy pension_case_fixture from '/docker-entrypoint-initdb.d/pension_case.csv' with (format csv, header true);

insert into pension_case
select * from pension_case_fixture
on conflict (pension_case_id) do update set
    pensioner_uin = excluded.pensioner_uin,
    spouse_uin = excluded.spouse_uin,
    marriage_mrn = excluded.marriage_mrn,
    pension_status = excluded.pension_status,
    payment_status = excluded.payment_status,
    survivor_eligible = excluded.survivor_eligible,
    last_payment_date = excluded.last_payment_date,
    account_life_status = excluded.account_life_status,
    observed_at = excluded.observed_at,
    source_system = excluded.source_system;

insert into sipf_pension_payment (pensioner_uin, payment_status)
select pensioner_uin, payment_status from pension_case_fixture
on conflict (pensioner_uin) do update set
    payment_status = excluded.payment_status;

insert into sipf_survivor_benefit (spouse_uin, survivor_eligible)
select spouse_uin, survivor_eligible from pension_case_fixture where spouse_uin is not null
on conflict (spouse_uin) do update set
    survivor_eligible = excluded.survivor_eligible;
