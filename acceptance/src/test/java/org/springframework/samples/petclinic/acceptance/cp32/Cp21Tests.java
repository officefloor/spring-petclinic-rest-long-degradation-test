package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp21 audit-create: UPDATED by cp32 (global-id) — Redesign owner identity */
@Tag("cp21")
class Cp21Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Redesign owner identity.
		// TODO: assert the UPDATED behaviour of "audit-create" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
