fn extract(source_response, context) {
    let domain = source_response["data"]["domainData"];
    if domain.contains("farmerRegistered") {
        return #{outcome: "match", facts: #{farmer_registered: domain["farmerRegistered"], data_use_authorized: domain["dataUseAuthorized"], active_smallholder_farmer: domain["activeSmallholderFarmer"], active_farm_parcel: domain["activeFarmParcel"], crop_declared_for_season: domain["cropDeclaredForSeason"], district_climate_risk_active: domain["districtClimateRiskActive"], voucher_entitlement_current: domain["voucherEntitlementCurrent"], voucher_not_redeemed: domain["voucherNotRedeemed"]}};
    }
    #{outcome: "match", facts: #{registered_herd: domain["registeredHerd"], herd_vaccination_current: domain["herdVaccinationCurrent"], origin_district_not_quarantined_for_species: domain["originDistrictNotQuarantinedForSpecies"], destination_district_open: domain["destinationDistrictOpen"], no_conflicting_open_movement_permit: domain["noConflictingOpenMovementPermit"]}}
}
