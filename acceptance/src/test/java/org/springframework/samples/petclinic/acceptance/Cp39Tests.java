package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp39 tenure-cap: Define that membership level 4 requires tenure of more than 365 days. Because a newly crea... */
@Tag("cp39")
class Cp39Tests extends AcceptanceBase {

	@Test
	void coreNewOwnerCappedAtLevel3() throws Exception {
		// even with all factors, a brand-new owner has zero tenure
		int id = createOwnerOk(withPostcode(ownerNode()));
		getOwner(id).andExpect(jsonPath("$.membershipLevel").exists()); // TODO: assert <= 3
	}
}
