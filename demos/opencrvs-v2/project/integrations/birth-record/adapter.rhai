fn non_empty(value) {
    value != () && type_of(value) == "string" && value.len > 0
}

fn consult(ctx) {
    let exact_registration = #{
        type: "exact",
        term: ctx.input.registration_number
    };
    let clause = #{ eventType: "birth" };
    clause["legalStatuses.REGISTERED.registrationNumber"] = exact_registration;
    let request_body = #{
        query: #{
            type: "and",
            clauses: [clause]
        },
        limit: 2,
        offset: 0
    };
    let response = source.post_json("/events/events/search", request_body);

    if response.status != 200 {
        return result.fail(failure.source_rejected);
    }
    if response.body.results == () || type_of(response.body.results) != "array" {
        return result.fail(failure.source_rejected);
    }

    let records = response.body.results;
    if records.len == 0 {
        return result.no_match();
    }
    if records.len > 1 {
        return result.ambiguous();
    }

    let record = records[0];
    if record.type != "birth" {
        return result.fail(failure.subject_mismatch);
    }
    if record.trackingId != ctx.input.tracking_id {
        return result.fail(failure.subject_mismatch);
    }

    let declaration = record.declaration;
    let mother_name = declaration["mother.name"];
    let informant_relation = declaration["informant.relation"];
    let mother_recorded = type_of(mother_name) == "map"
        && non_empty(mother_name.firstname)
        && non_empty(mother_name.surname);
    let informant_is_mother = non_empty(informant_relation)
        && xw.text.lower_ascii(informant_relation) == "mother";

    result.match(#{
        event_type_birth: true,
        tracking_id_matches: true,
        registration_number_matches:
            record.legalStatuses.REGISTERED.registrationNumber
                == ctx.input.registration_number,
        child_national_id_matches:
            declaration["child.nid"] == ctx.input.child_national_id,
        mother_recorded_on_birth: mother_recorded,
        informant_is_mother: informant_is_mother
    })
}
