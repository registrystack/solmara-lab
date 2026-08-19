fn derive(facts, selectors, evaluation_context) {
    [#{concept_id: "https://id.registrystack.org/solmara/concept/person-is-deceased", value: required(facts["deceased"], "required_fact_missing")}]
}
