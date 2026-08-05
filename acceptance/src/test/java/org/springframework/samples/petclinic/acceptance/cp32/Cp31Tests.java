package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.JsonNode;

/** cp31 check-digit, UPDATED by cp32: still the Luhn digit over the customerCode digits, now over the
 *  region-and-hash code. Recomputed from the returned customerCode. */
@Tag("cp31")
class Cp31Tests extends AcceptanceBase {

	@Test
	void coreCheckDigitIsLuhnOfNewCode() throws Exception {
		JsonNode r = fetchOwner(createOwnerOk(knownOwner("Sydney")));
		assertEquals(luhn(r.get("customerCode").asText()), r.get("checkDigit").asInt());
	}
}
