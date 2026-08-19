fn extract(source_response, context) {
    let rows = source_response["rows"];
    if rows.len == 0 { return #{outcome: "no_match"}; }
    if rows.len > 1 { return #{outcome: "ambiguous"}; }
    let row = rows[0];
    #{outcome: "match", facts: #{uin: row["uin"], birth_date: row["birth_date"], birth_registered: !is_missing(row["birth_brn"])}}
}
