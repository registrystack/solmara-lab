fn extract(source_response, context) {
    let rows = source_response["rows"];
    if rows.len == 0 { return #{outcome: "no_match"}; }
    if rows.len > 1 { return #{outcome: "ambiguous"}; }
    #{outcome: "match", facts: rows[0]}
}
