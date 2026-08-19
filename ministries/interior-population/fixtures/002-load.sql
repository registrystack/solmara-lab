create temporary table population_person_fixture
    (like population_person including defaults);

copy population_person_fixture from '/docker-entrypoint-initdb.d/population_person.csv' with (format csv, header true);

insert into population_person
select * from population_person_fixture
on conflict (uin) do update set
    person_id = excluded.person_id,
    legacy_nid = excluded.legacy_nid,
    given_name = excluded.given_name,
    family_name = excluded.family_name,
    birth_date = excluded.birth_date,
    sex = excluded.sex,
    district_code = excluded.district_code,
    address_area = excluded.address_area,
    settlement_type = excluded.settlement_type,
    identity_status = excluded.identity_status,
    pending_merge_with_uin = excluded.pending_merge_with_uin,
    match_basis = excluded.match_basis,
    alive = excluded.alive,
    birth_brn = excluded.birth_brn,
    updated_at = excluded.updated_at,
    observed_at = excluded.observed_at,
    source_system = excluded.source_system;
