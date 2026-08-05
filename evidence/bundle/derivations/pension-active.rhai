fn derive(facts, selectors, evaluation_context) {
    if required(facts["pensioner_uin"], "required_fact_missing") != selectors["subject"]["values"]["uin"] {
        throw("derivation_input_error");
    }
    [#{concept_id: "https://id.registrystack.org/solmara/concept/pension-payment-active", value: required(facts["payment_status"], "required_fact_missing") == "active"}]
}
