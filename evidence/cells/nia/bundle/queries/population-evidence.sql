SELECT uin, identity_status, alive
FROM population_evidence
WHERE uin = :uin
LIMIT 2;
