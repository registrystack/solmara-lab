SELECT uin, poverty_band
FROM poverty_evidence
WHERE uin = :uin
LIMIT 2;
