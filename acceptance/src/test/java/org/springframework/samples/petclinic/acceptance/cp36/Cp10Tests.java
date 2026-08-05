package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp10 household-duplicate, UPDATED by cp36: the household is keyed by the computed householdId
 *  (lastName + postcode). Two owners with the same lastName + postcode collide with 409 (no
 *  sharesHousehold), even with different addresses. */
@Tag("cp10")
class Cp10Tests extends AcceptanceBase {

	@Test
	void coreSameLastNameAndPostcodeRejected() throws Exception {
		String lastName = uniqueLastName();
		ObjectNode a = ownerNode();
		a.put("lastName", lastName);
		a.put("postcode", "2000");
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // same lastName + postcode, different address/telephone
		b.put("lastName", lastName);
		b.put("postcode", "2000");
		createOwner(b).andExpect(status().isConflict());
	}
}
