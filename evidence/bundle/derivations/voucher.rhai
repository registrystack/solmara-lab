fn derive(facts, selectors, evaluation_context) {
    if required(facts["farmer_id"], "required_fact_missing") != selectors["subject"]["values"]["farmer_id"] {
        throw("derivation_input_error");
    }
    let registered = required(facts["farmer_registered"], "required_fact_missing");
    let authorized = required(facts["data_use_authorized"], "required_fact_missing");
    let eligible = registered && authorized &&
        required(facts["active_smallholder_farmer"], "required_fact_missing") &&
        required(facts["active_farm_parcel"], "required_fact_missing") &&
        required(facts["crop_declared_for_season"], "required_fact_missing") &&
        required(facts["district_climate_risk_active"], "required_fact_missing") &&
        required(facts["voucher_entitlement_current"], "required_fact_missing") &&
        required(facts["voucher_not_redeemed"], "required_fact_missing");
    [
        #{concept_id: "https://id.registrystack.org/solmara/concept/farmer-registered", value: registered},
        #{concept_id: "https://id.registrystack.org/solmara/concept/data-use-authorized-for-purpose", value: authorized},
        #{concept_id: "https://id.registrystack.org/solmara/concept/eligible-for-climate-smart-input-voucher", value: eligible}
    ]
}
