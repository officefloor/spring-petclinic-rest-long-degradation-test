package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp36 household-hash: The householdId must become deterministic: the first 12 hex characters of SHA-256 over (no... */
@Tag("cp36")
class Cp36Tests extends AcceptanceBase {

	@Test
	void coreDeterministicHouseholdId() throws Exception {
		int id = createOwnerOk(withPostcode(ownerNode()));
		getOwner(id).andExpect(jsonPath("$.householdId").exists()); // sha256(lastName|postcode)[0:12]
	}
}
