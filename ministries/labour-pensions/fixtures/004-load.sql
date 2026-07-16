copy pension_case from '/docker-entrypoint-initdb.d/pension_case.csv' with (format csv, header true);

insert into sipf_pension_payment (pensioner_uin, payment_status)
select pensioner_uin, payment_status from pension_case;

insert into sipf_survivor_benefit (spouse_uin, survivor_eligible)
select spouse_uin, survivor_eligible from pension_case where spouse_uin is not null;
