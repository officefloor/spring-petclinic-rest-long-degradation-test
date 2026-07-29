package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp02: reject a new owner with the same last name AND telephone as an existing one (409). */
@Tag("cp02")
class Cp02Tests extends AcceptanceBase {

	@Test
	void coreRejectsSameLastNameAndTelephone() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // distinct address/city
		b.put("lastName", a.get("lastName").asText());
		b.put("telephone", a.get("telephone").asText());
		createOwner(b).andExpect(status().isConflict());
	}

	@Test
	void functionalityAllowsSameLastNameDifferentTelephone() throws Exception {
		ObjectNode a = ownerNode();
		createOwnerOk(a);
		ObjectNode b = ownerNode(); // same last name, its own unique telephone
		b.put("lastName", a.get("lastName").asText());
		createOwner(b).andExpect(status().is2xxSuccessful());
	}
}
