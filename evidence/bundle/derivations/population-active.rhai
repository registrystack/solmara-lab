fn derive(facts, selectors, evaluation_context) {
    if required(facts["uin"], "required_fact_missing") != selectors["subject"]["values"]["uin"] {
        throw("derivation_input_error");
    }
    let active = required(facts["identity_status"], "required_fact_missing") == "active" &&
        required(facts["alive"], "required_fact_missing");
    [#{concept_id: evaluation_context["parameters"]["concept_id"], value: active}]
}
