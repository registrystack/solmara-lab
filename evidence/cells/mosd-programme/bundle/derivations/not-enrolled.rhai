fn derive(facts, selectors, evaluation_context) {
    [#{concept_id: "https://id.registrystack.org/solmara/concept/not-already-enrolled", value: !required(facts["duplicate_flag"], "required_fact_missing")}]
}
