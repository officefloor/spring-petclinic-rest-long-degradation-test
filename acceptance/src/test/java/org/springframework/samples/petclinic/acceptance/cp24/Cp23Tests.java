package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp23 tier-gold: UPDATED by cp24 (membership-levels) — Replace the string membership tier with a numeric 'membershipLevel' from 1 to 3 on creation: start at 1; add 1 when an email is present; add 1 when namesakeCount is 0; cap at 3 (level 4 is reserved for tenure) */
@Tag("cp23")
class Cp23Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. Replace the string membership tier with a numeric 'membershipLevel' from 1 to 3 on creation: start at 1; add 1 when an email is present; add 1 when namesakeCount is 0; cap at 3 (level 4 is reserved for tenure).
		// TODO: assert the UPDATED behaviour of "tier-gold" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
