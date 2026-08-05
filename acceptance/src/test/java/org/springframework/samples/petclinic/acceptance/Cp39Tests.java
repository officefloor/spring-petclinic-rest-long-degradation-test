package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp39 tenure-cap: level 4 requires tenure over 365 days, so a brand-new owner (zero tenure)
 *  never exceeds level 3. A new owner with an email and no namesake maxes the pre-tenure factors,
 *  and must land at level 3, not 4. */
@Tag("cp39")
class Cp39Tests extends AcceptanceBase {

	@Test
	void coreNewOwnerCappedAtLevel3() throws Exception {
		ObjectNode o = withPostcode(ownerNode());
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipLevel").value(3));
	}
}
