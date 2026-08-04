package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp14 membership-number: Assign 'membershipNumber' formatted '<customerCode>-M<YY>' where YY is the last two digits... */
@Tag("cp14")
class Cp14Tests extends AcceptanceBase {

	@Test
	void coreAssignsMembershipNumber() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.membershipNumber").exists()); // TODO: <customerCode>-M<YY>
	}
}
