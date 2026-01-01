from google_forms import debug_dump_latest_response

FORM_ID = "1MemCidpD0DBk65H5IufSnnB0PWqKNGrmvAGVXabeIiw"

payload = debug_dump_latest_response(
    FORM_ID,
    out_json_path="data/forms_latest_response_debug.json"
)

print("OK:", payload.get("ok"))
print("responseId:", payload.get("responseId"))
print("answers_by_title:")
for k, v in (payload.get("answers_by_title") or {}).items():
    print(" -", k, "=>", v)