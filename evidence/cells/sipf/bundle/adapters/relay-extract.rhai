fn extract(source_response, context) {
    let domain = source_response["data"]["domainData"];
    if domain.contains("paymentStatus") { return #{outcome: "match", facts: #{payment_status: domain["paymentStatus"]}}; }
    #{outcome: "match", facts: #{survivor_eligible: domain["survivorEligible"]}}
}
