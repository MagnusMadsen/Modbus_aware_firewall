# constants.py samler de faste Modbus-værdier.
    # Altså den bruges udelukkende til at definere og forklare de faste værdier, 
    # som parseren er bygget omkring. Den indeholder ingen logik i sig selv.
# Den bruges af parser.py, request.py og response.py til at afgøre om en packet er Modbus TCP,
# og hvilken type register en bestemt Modbus function code arbejder med.


# Modbus TCP bruger port 502.
# parser.py bruger denne konstant til kun at forsøge Modbus-parsing på TCP-trafik hvor source eller destination port er 502.
MODBUS_PORT = 502

# Mapping for Modbus read function codes.
# talet er function code fra Modbus-pakken.
# Værdien er den registertype resten af systemet bruger i events, modbus_register_state og critical_registers.
# 1 læser coils, 2 læser discrete inputs, 3 læser holding registers, og 4 læser input registers.
READ_REGISTER_TYPES = {
    1: "coil",
    2: "discrete_input",
    3: "holding_register",
    4: "input_register",
}

# Mapping for Modbus write function codes.
# 5 skriver én coil, 6 skriver ét holding register, 15 skriver flere coils, og 16 skriver flere holding registers.
# Coils er 1-bit værdier, mens holding registers er 16-bit registerværdier.
WRITE_REGISTER_TYPES = {
    5: "coil",
    6: "holding_register",
    15: "coil",
    16: "holding_register",
}

# SUPPORTED_FUNCTION_CODES er den samlede liste over function codes parseren håndterer.
# Hvis parser.py ser en Modbus function code som ikke findes her, returneres pakken uden Modbus-dekodning.
# Det begrænser projektet til de Modbus-operationer vi aktivt parser og viser i dashboardet.
SUPPORTED_FUNCTION_CODES = {
    *READ_REGISTER_TYPES.keys(),
    *WRITE_REGISTER_TYPES.keys(),
}