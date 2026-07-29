package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp03: telephone must be unique across all owners (409). */
@Tag("cp03")
class Cp03Tests extends AcceptanceBase {

	@Test
	void coreRejectsDuplicateTelephone() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // different name/address/city
		b.put("telephone", a.get("telephone").asText());
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsDistinctTelephones() throws Exception {
		createOwnerOk(ownerNode());
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}
}
