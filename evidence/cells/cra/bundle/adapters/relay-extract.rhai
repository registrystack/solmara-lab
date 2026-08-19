fn extract(source_response, context) {
    let domain = source_response["data"]["domainData"];
    if domain.contains("deceased") { return #{outcome: "match", facts: #{deceased: domain["deceased"]}}; }
    #{outcome: "match", facts: #{linkedUin: domain["linkedUin"]}}
}
