package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;

/** check-digit: 'checkDigit' is the Luhn check digit over the digits of the customerCode. The
 * test recomputes Luhn from the returned customerCode and asserts the exact digit. */
@Tag("cp31")
class Cp31Tests extends AcceptanceBase {

	@Test
	void coreCheckDigitIsLuhnOfCustomerCode() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(ownerNode()));
		assertEquals(luhn(r.get("customerCode").asText()), r.get("checkDigit").asInt());
	}
}
