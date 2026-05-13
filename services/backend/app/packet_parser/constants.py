# Konstanter og mapping-tabeller.

MODBUS_PORT = 502

READ_REGISTER_TYPES = {
    1: "coil",
    2: "discrete_input",
    3: "holding_register",
    4: "input_register",
}

WRITE_REGISTER_TYPES = {
    5: "coil",
    6: "holding_register",
    15: "coil",
    16: "holding_register",
}

SUPPORTED_FUNCTION_CODES = {
    *READ_REGISTER_TYPES.keys(),
    *WRITE_REGISTER_TYPES.keys(),
}