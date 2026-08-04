package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp36 household-hash: UPDATED by cp60 (identity-v2) — Release version 2 of the owner identity */
@Tag("cp36")
class Cp36Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Release version 2 of the owner identity.
		// TODO: assert the UPDATED behaviour of "household-hash" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
