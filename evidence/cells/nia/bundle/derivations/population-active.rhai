fn derive(facts, selectors, evaluation_context) {
    let active = required(facts["identity_status"], "required_fact_missing") == "active" && required(facts["alive"], "required_fact_missing");
    [#{concept_id: evaluation_context["parameters"]["concept_id"], value: active}]
}
