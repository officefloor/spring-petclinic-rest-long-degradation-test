package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp23 tier-gold: UPDATED by cp40 (membership-points) — Replace the level rules with a points system: start at 0; add 2 when an email is present; add 1 when namesakeCount is 0; add 2 for a household of 3 or more; add 3 for tenure over 365 days */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Replace the level rules with a points system: start at 0; add 2 when an email is present; add 1 when namesakeCount is 0; add 2 for a household of 3 or more; add 3 for tenure over 365 days.
		// TODO: assert the UPDATED behaviour of "tier-gold" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
