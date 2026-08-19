fn prepare(selectors, context) {
    let parameters = context["parameters"];
    let subject = selectors["subject"]["values"];
    #{query: [#{name: "fields", value: parameters["fields"]}], body: #{selectors: #{uin: subject["uin"]}}}
}
