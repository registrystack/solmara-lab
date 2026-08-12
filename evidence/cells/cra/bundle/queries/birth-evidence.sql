SELECT uin, birth_date, birth_brn
FROM birth_evidence
WHERE uin = :uin
LIMIT 2;
