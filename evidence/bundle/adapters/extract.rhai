fn extract(source_response, parameters) {
    let records = source_response["data"];
    let has_more = source_response["pagination"]["has_more"];
    if records.len == 0 {
        if has_more { throw("source_protocol_error"); }
        return #{outcome: "no_match"};
    }
    if records.len > 1 || has_more {
        return #{outcome: "ambiguous"};
    }
    let record = records[0];
    // Relay preserves a nullable birth-registration number. Minimize that
    // identifier into the only fact the derivation needs before validation.
    if record.contains("birth_brn") {
        return #{
            outcome: "match",
            facts: #{
                uin: record["uin"],
                birth_date: record["birth_date"],
                birth_registered: !is_missing(record["birth_brn"]),
                deceased: record["deceased"]
            }
        };
    }
    #{outcome: "match", facts: record}
}
