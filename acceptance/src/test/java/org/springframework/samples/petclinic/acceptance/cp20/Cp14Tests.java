package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** cp14 membership-number: UPDATED by cp20 (business-day) — The default registration date must now fall on a business day: when the server date is a Saturday or Sunday, roll it forward to the next Monday and use that as 'registrationDate' */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreUpdatedBehaviour() throws Exception {
		// This rule changed. The default registration date must now fall on a business day: when the server date is a Saturday or Sunday, roll it forward to the next Monday and use that as 'registrationDate'.
		// TODO: assert the UPDATED behaviour of "membership-number" under the new spec.
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(status().is2xxSuccessful());
	}
}
