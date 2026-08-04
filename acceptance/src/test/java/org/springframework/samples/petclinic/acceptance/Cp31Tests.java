package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp31 check-digit: Return 'checkDigit' = a single Luhn check digit computed over the digits of the customerCo... */
@Tag("cp31")
class Cp31Tests extends AcceptanceBase {

	@Test
	void coreReturnsCheckDigit() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.checkDigit").exists()); // Luhn over customerCode digits
	}
}
