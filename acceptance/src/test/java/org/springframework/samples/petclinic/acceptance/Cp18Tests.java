package org.springframework.samples.petclinic.acceptance;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import tools.jackson.databind.node.ObjectNode;

/** cp18: locality = "local" if the city is the most common among existing owners, else "remote". */
@Tag("cp18")
class Cp18Tests extends AcceptanceBase {

	@Test
	void coreLocalWhenCityIsMostCommon() throws Exception {
		String hub = uniqueCity();
		// Make `hub` clearly the most common city (seed cities have only a few each).
		for (int i = 0; i < 6; i++) {
			ObjectNode o = ownerNode();
			o.put("city", hub);
			createOwnerOk(o);
		}
		ObjectNode inHub = ownerNode();
		inHub.put("city", hub);
		assertEquals("local", fetchOwner(createOwnerOk(inHub)).get("locality").asText());

		ObjectNode elsewhere = ownerNode(); // its own unique, rare city
		assertEquals("remote", fetchOwner(createOwnerOk(elsewhere)).get("locality").asText());
	}
}
