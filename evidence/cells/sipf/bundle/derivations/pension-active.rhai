fn derive(facts, selectors, evaluation_context) {
    [#{concept_id: "https://id.registrystack.org/solmara/concept/pension-payment-active", value: required(facts["payment_status"], "required_fact_missing") == "active"}]
}
