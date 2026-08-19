fn derive(facts, selectors, evaluation_context) {
    let registered = required(facts["registered_herd"], "required_fact_missing");
    let not_quarantined = required(facts["origin_district_not_quarantined_for_species"], "required_fact_missing");
    let eligible = registered && not_quarantined && required(facts["herd_vaccination_current"], "required_fact_missing") && required(facts["destination_district_open"], "required_fact_missing") && required(facts["no_conflicting_open_movement_permit"], "required_fact_missing");
    [
        #{concept_id: "https://id.registrystack.org/solmara/concept/registered-herd", value: registered},
        #{concept_id: "https://id.registrystack.org/solmara/concept/origin-district-not-quarantined-for-species", value: not_quarantined},
        #{concept_id: "https://id.registrystack.org/solmara/concept/eligible-for-livestock-movement-permit", value: eligible}
    ]
}
