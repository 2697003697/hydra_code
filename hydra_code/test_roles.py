from orchestration.roles import ModelRole, ROLE_DEFINITIONS

print("Checking ModelRole enum:")
for role in ModelRole:
    print(f"- {role.name}: {role.value}")

print("\nChecking ROLE_DEFINITIONS:")
if ModelRole.CHAT in ROLE_DEFINITIONS:
    print(f"SUCCESS: {ModelRole.CHAT.name} definition found.")
    print(f"Description: {ROLE_DEFINITIONS[ModelRole.CHAT].description}")
else:
    print(f"FAILURE: {ModelRole.CHAT.name} definition NOT found.")
