package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp11 shares-household: UPDATED by cp28 (identity-key) — Consolidate all duplicate detection into a single derived 'identityKey' = normalizedTelephone + '|' + (email or empty) + '|' + householdId, and reject with 409 when a new owner's identityKey matches an existing owner */
@Tag("cp11")
class Cp11Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Consolidate all duplicate detection into a single derived 'identityKey' = normalizedTelephone + '|' + (email or empty) + '|' + householdId, and reject with 409 when a new owner's identityKey matches an existing owner.
		// TODO: assert the UPDATED behaviour of "shares-household" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
