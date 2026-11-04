
from pydantic import BaseModel, Field


class NumF(BaseModel):
    value: float | None = Field(None, description="Number only, no commas or currency. null if not stated.")
    quote: str | None = Field(None, description="Exact text copied from the document.")


class StrF(BaseModel):
    value: str | None = None
    quote: str | None = None


class SupplierDoc(BaseModel):
    # --- identity (brief: report supplier and item; item code links to the purchase request) ---
    supplier_name: StrF
    item_code: StrF = Field(description="Single letter A-E as printed in the Item column")

    # --- quantity and price (Reject 1, Needs 1, Needs 2) ---
    quantity: NumF
    unit_price: NumF = Field(description="Unit price exactly as printed")

    # --- the numbers that must add up (Needs 6) ---
    line_amount: NumF = Field(description="Amount column exactly as printed. Do NOT recalculate.")
    subtotal: NumF
    total: NumF

    # --- VAT shown separately at 15% (Needs 5) ---
    vat_rate_pct: NumF = Field(description="Percentage on a separate VAT line. null if there is no VAT line.")
    vat_amount: NumF = Field(description="Amount on a separate VAT line. null if there is no VAT line.")

    # --- registration (Reject 4) ---
    tin: StrF = Field(description="TIN number. null if no number is given.")
    bin: StrF = Field(description="BIN number. null if no number is given.")

    # --- advance (Reject 2) ---
    advance_pct: NumF = Field(description="Advance percent due with the PO. 0 if the document says no advance.")

    # --- payment terms (Needs 3) ---
    payment_days_min: NumF = Field(description="Lower number of days in the payment clause. Same as max if one number.")
    payment_days_max: NumF = Field(description="Upper number of days in the payment clause. Same as min if one number.")
    payment_counted_from: StrF = Field(
        description="What the payment days are counted from, as stated: 'delivery', 'PO', or null if not stated.")

    # --- delivery (Reject 5, Needs 4) ---
    delivery_value: NumF = Field(description="Delivery time number exactly as printed, e.g. 4 for '4 weeks'.")
    delivery_unit: StrF = Field(description="'days' or 'weeks', as printed.")

    # --- late-delivery penalty (Reject 3, penalty note) ---
    penalty_pct_per_week: NumF = Field(
        description="Late-delivery penalty percent per week. null if there is no penalty clause.")

    # --- validity (Needs 7) ---
    validity_days: NumF

    # --- "if you are not sure, needs a person" ---
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="Anything odd: repeated sentences, contradictions, unreadable parts. Empty list if none.",
    )
