from typing import Optional
from pydantic import BaseModel, Field


class NumF(BaseModel):
    value: Optional[float] = Field(None, description="Number only, no commas or currency. null if not stated.")
    quote: Optional[str] = Field(None, description="Exact text copied from the document.")


class StrF(BaseModel):
    value: Optional[str] = None
    quote: Optional[str] = None


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
    payment_counted_from: StrF = Field(description="What the payment days are counted from, as stated: 'delivery', 'PO', or null if not stated.")

    # --- delivery (Reject 5, Needs 4) ---
    delivery_value: NumF = Field(description="Delivery time number exactly as printed, e.g. 4 for '4 weeks'.")
    delivery_unit: StrF = Field(description="'days' or 'weeks', as printed.")

    # --- late-delivery penalty (Reject 3, penalty note) ---
    penalty_pct_per_week: NumF = Field(description="Late-delivery penalty percent per week. null if there is no penalty clause.")

    # --- validity (Needs 7) ---
    validity_days: NumF

    # --- "if you are not sure, needs a person" ---
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="Anything odd: repeated sentences, contradictions, unreadable parts. Empty list if none.",
    )


SYSTEM_PROMPT = """You are a document READER for a procurement checking pipeline.
You will receive the plain text of ONE supplier quotation with its terms and conditions.
Return ONLY a JSON object that follows the provided schema. No explanations, no markdown.
 
YOUR JOB IS TO COPY WHAT THE DOCUMENT SAYS. YOU DO NOT JUDGE IT.
- Do NOT decide whether anything is acceptable, good, bad, clear, unclear or compliant.
- Do NOT calculate, convert or fix numbers. If Amount says 322,000, report 322,000 even if qty x price disagrees.
- Do NOT use outside knowledge, and do NOT fill gaps with typical values.
 
RULES FOR EVERY FIELD
1. `value` must come from the document. If it is not stated, value is null.
2. `quote` must be copied EXACTLY, character for character, from the document text. Keep it short (one line or clause).
3. If value is null but the document says something about that field (for example "details available on request"), put that sentence in `quote`. If the document says nothing about it, quote is null too.
4. Numbers: digits only. Remove commas and currency labels. 12,000 -> 12000.
 
FIELD GUIDE (what each field means and where to find it)
- supplier_name: company name at the top of the quotation.
- item_code: the single letter (A, B, C, D or E) at the start of the item row, under the "Item" column header. Example row "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00" -> "A".
- quantity: the Qty column of the item row.
- unit_price: the Unit price column of the item row.
- line_amount: the Amount column of the item row, exactly as printed.
- subtotal: the number on the "Subtotal" line.
- total: the number on the "Total" line.
- vat_rate_pct: the percentage on a separate VAT line, e.g. "VAT 15%" -> 15.
- vat_amount: the amount on that separate VAT line.
- tin: the number after "TIN:". bin: the number after "BIN:". Copy them as printed, including dashes.
- advance_pct: the advance percentage in the payment clause.
- payment_days_min / payment_days_max: the number of days in the payment clause.
- payment_counted_from: what those payment days are counted from.
- delivery_value / delivery_unit: the delivery time in the delivery clause.
- penalty_pct_per_week: the late-delivery penalty percentage.
- validity_days: the number of days in the validity clause.
 
SPECIFIC CASES
- No advance: "No advance payment required" -> advance_pct = 0, quote that sentence.
- Payment days: copy the numbers as written. "within 45 days" -> min 45, max 45. "30 to 90 days" -> min 30, max 90.
- payment_counted_from: "of delivery" or "after delivery" -> "delivery". "of PO" -> "PO". If the clause does not say, null.
- Delivery: copy the number and unit as written. "4 weeks" -> delivery_value 4, delivery_unit "weeks". Do NOT convert.
- Penalty: only a clause that charges the supplier for late delivery counts. If there is none, penalty_pct_per_week value and quote are null.
- TIN/BIN: value is the number only. If no number is given, value is null.
- VAT: vat_rate_pct and vat_amount only from a separate VAT line. If prices are described as VAT included and there is no VAT line, both values are null; quote the "VAT included" text in vat_rate_pct.quote.
- Missing subtotal or total line: value and quote null.
- Repeated or contradictory sentences: do not double count. Report the value, and add a short note to extraction_notes.
- If something is ambiguous and none of the above covers it, use null and explain in extraction_notes. A null is always better than a guess.
"""