package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp03 telephone-unique: Reject creating an owner whose normalized telephone is already used by any other owner. Re... */
@Tag("cp03")
class Cp03Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateTelephone() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode();
		b.put("telephone", a.get("telephone").asText());
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsDistinctTelephone() throws Exception {
		createOwnerOk(ownerNode());
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}
}
