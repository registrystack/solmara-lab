fn derive(facts, selectors, evaluation_context) {
    required(facts["linkedUin"], "required_fact_missing");
    [#{concept_id: "https://id.registrystack.org/solmara/concept/civil-record-linked", value: true}]
}
