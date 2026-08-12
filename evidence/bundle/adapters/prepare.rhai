fn prepare(selectors, context) {
    let parameters = context["parameters"];
    let selector_field = parameters["selectorField"];
    let subject = selectors["subject"];
    let selector_value = subject["values"]["uin"];
    if selector_field == "farmer_id" {
        selector_value = subject["values"]["farmer_id"];
    }
    #{
        query: [
            #{name: selector_field, value: selector_value},
            #{name: "fields", value: parameters["providerFields"]},
            #{name: "limit", value: parameters["resultLimit"]}
        ],
        body: ()
    }
}
