package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** membership-number: the membershipNumber field is removed (unified into the
 * memberId). */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreMembershipNumberRemoved() throws Exception {
		int id = createOwnerOk(knownOwner("Sydney"));
		getOwner(id).andExpect(jsonPath("$.membershipNumber").doesNotExist());
	}
}
