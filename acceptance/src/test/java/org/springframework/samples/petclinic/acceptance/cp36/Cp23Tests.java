package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp23 tier-gold: UPDATED by cp36 (household-hash) — The householdId must become deterministic: the first 12 hex characters of SHA-256 over (normalizedLastName + '|' + postcode), so owners with the same lastName and postcode share it automatically */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. The householdId must become deterministic: the first 12 hex characters of SHA-256 over (normalizedLastName + '|' + postcode), so owners with the same lastName and postcode share it automatically.
		// TODO: assert the UPDATED behaviour of "tier-gold" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
