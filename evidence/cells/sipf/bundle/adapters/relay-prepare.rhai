fn prepare(selectors, context) {
    let parameters = context["parameters"];
    let subject = selectors["subject"]["values"];
    let relay_selectors = #{};
    if parameters["selectorField"] == "pensionerUin" {
        relay_selectors["pensionerUin"] = subject["uin"];
    } else if parameters["selectorField"] == "spouseUin" {
        relay_selectors["spouseUin"] = subject["uin"];
    } else {
        throw("invalid_selector_field");
    }
    #{query: [#{name: "fields", value: parameters["fields"]}], body: #{selectors: relay_selectors}}
}
