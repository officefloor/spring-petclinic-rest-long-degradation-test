package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** cp15 membership-tier: Return 'membershipTier': 'SILVER' when namesakeCount is 0 and an email is present, otherwi... */
@Tag("cp15")
class Cp15Tests extends AcceptanceBase {

	@Test
	void coreSilverWhenUniqueWithEmail() throws Exception {
		ObjectNode o = ownerNode();
		o.put("firstName", "Uniq"); o.put("lastName", "solotier");
		o.put("email", uniqueEmail());
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.membershipTier").value("SILVER"));
	}

	@Test
	void functionalityBronzeWhenNoEmail() throws Exception {
		int id = createOwnerOk(ownerNode());
		getOwner(id).andExpect(jsonPath("$.membershipTier").value("BRONZE"));
	}
}
